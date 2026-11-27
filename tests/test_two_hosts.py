"""The desk / research-host split (AQ_ROLE): no agent may start on the desk, the poller
does only its own host's half, and the dashboard reads the research host's synced files
without trusting them."""
import json
import os
import subprocess
import textwrap
import time

import pytest

import dashboard
from conftest import REPO_ROOT

HARNESS = os.path.join(REPO_ROOT, "harness")
UUID = "0123abcd-0000-4000-8000-00000000beef"


def run(script, *args, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([os.path.join(HARNESS, script), *args], capture_output=True,
                          text=True, timeout=60, env=e, cwd=REPO_ROOT)


# ----------------------------------------------------------------- role resolution

def _role(tmp_path, env_role=None, dotenv=None):
    (tmp_path / "harness").mkdir(exist_ok=True)
    if dotenv is not None:
        (tmp_path / ".env").write_text(dotenv)
    script = textwrap.dedent("""\
        SL_REPO="$1"
        eval "$(sed -n '/^aq_role() {/,/^}/p' "$2")"
        aq_role
        """)
    e = {k: v for k, v in os.environ.items() if k != "AQ_ROLE"}
    if env_role is not None:
        e["AQ_ROLE"] = env_role
    p = subprocess.run(["bash", "-c", script, "bash", str(tmp_path),
                        os.path.join(HARNESS, "session_lib.sh")],
                       capture_output=True, text=True, env=e, timeout=30)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def test_role_comes_from_dotenv(tmp_path):
    assert _role(tmp_path, dotenv="X=1\nAQ_ROLE=desk\n") == "desk"
    assert _role(tmp_path, dotenv="AQ_ROLE='research'\n") == "research"


def test_environment_wins_over_dotenv(tmp_path):
    assert _role(tmp_path, env_role="research", dotenv="AQ_ROLE=desk\n") == "research"


@pytest.mark.parametrize("dotenv", ["", "AQ_ROLE=\n", "AQ_ROLE=trader\n"])
def test_no_or_unknown_role_is_the_old_single_host(tmp_path, dotenv):
    assert _role(tmp_path, dotenv=dotenv) == "all"


# ----------------------------------------------------- no agent may start on the desk

@pytest.mark.parametrize("script,args", [
    ("launch_research.sh", ["spot-btc"]),
    ("deploy_agent.sh", ["999999"]),
    ("revise_agent.sh", ["999999"]),
    ("resume_aborted.sh", [UUID]),
    ("agent_exec.sh", ["start", UUID, "/dev/null", "60", "opus", "x"]),
])
def test_every_launcher_refuses_on_the_desk(script, args):
    p = run(script, *args, env={"AQ_ROLE": "desk"})
    assert p.returncode == 5, (p.returncode, p.stdout, p.stderr)
    assert "trading desk" in p.stderr


def test_a_usage_error_is_still_a_usage_error_on_the_desk():
    p = run("launch_research.sh", "dogecoin", env={"AQ_ROLE": "desk"})
    assert p.returncode == 2


def test_the_nightly_batch_launches_nothing_on_the_desk():
    src = open(os.path.join(HARNESS, "nightly_research.sh")).read()
    guard = src.index('if [ "$(aq_role)" = desk ]')
    assert guard < src.index('"$CLAUDE_BIN" update'), "guard must precede any agent work"


def test_the_trading_installer_refuses_on_the_research_host():
    p = run("install_autostart.sh", env={"AQ_ROLE": "research"})
    assert p.returncode == 5 and "research host" in p.stderr


# -------------------------------------------------------------- the desk's launcher

def test_desk_launch_is_a_no_op_off_the_desk():
    p = run("desk_launch.sh", env={"AQ_ROLE": "research"})
    assert p.returncode == 0 and "not the desk" in p.stdout


@pytest.mark.parametrize("since", ["", "yesterday", "2026-11-27"])
def test_desk_launch_refuses_without_a_cutoff(since):
    """Without AQ_DESK_SINCE every historical `deployed` PR would qualify."""
    p = run("desk_launch.sh", "--dry-run", env={"AQ_ROLE": "desk", "AQ_DESK_SINCE": since or " "})
    assert p.returncode == 1 and "launching nothing" in p.stdout


def _fake_gh(tmp_path, prs, files):
    """A `gh` on PATH that answers `pr list` by running the real --jq over `prs`."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (tmp_path / "prs.json").write_text(json.dumps(prs))
    (tmp_path / "files.json").write_text(json.dumps(files))
    gh = bindir / "gh"
    gh.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        if [ "$1 $2" = "pr list" ]; then
          while [ $# -gt 0 ]; do [ "$1" = --jq ] && q="$2"; shift; done
          jq -r "$q" {tmp_path}/prs.json; exit
        fi
        if [ "$1" = api ]; then
          case "$2" in */files) jq -r '.[] | .filename' {tmp_path}/files.json; exit ;; esac
        fi
        exit 0
        """))
    gh.chmod(0o755)
    return {"PATH": f"{bindir}:{os.environ['PATH']}"}


def _label(*names):
    return [{"name": n} for n in names]


def test_desk_launch_picks_only_new_unlaunched_deployments(tmp_path):
    prs = [
        {"number": 30, "title": "new", "mergedAt": "2026-12-01T00:00:00Z",
         "labels": _label("deployed")},
        {"number": 27, "title": "old", "mergedAt": "2026-10-10T08:48:00Z",
         "labels": _label("deployed")},
        {"number": 31, "title": "done", "mergedAt": "2026-12-01T00:00:00Z",
         "labels": _label("deployed", "vps:launched")},
        {"number": 32, "title": "failed", "mergedAt": "2026-12-01T00:00:00Z",
         "labels": _label("deployed", "vps:launch-failed")},
        {"number": 33, "title": "archived", "mergedAt": "2026-12-01T00:00:00Z",
         "labels": _label("archived")},
    ]
    files = [{"filename": "live/spot-btc/new-thing/runner.py"},
             {"filename": "live/spot-btc/new-thing/meta.json"},
             {"filename": "code/spot-btc/new-thing/signal.py"}]
    env = _fake_gh(tmp_path, prs, files) | {"AQ_ROLE": "desk",
                                            "AQ_DESK_SINCE": "2026-11-27T18:00:00Z"}
    p = run("desk_launch.sh", "--dry-run", env=env)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "would launch PR #30" in p.stdout and "spot-btc/new-thing" in p.stdout
    for n in (27, 31, 32, 33):
        assert f"#{n}" not in p.stdout


# ------------------------------------------------------------ the poller's two halves

def _sweep(tmp_path, role):
    src = open(os.path.join(HARNESS, "poll_prs.sh")).read()
    body = src[src.index("sweep() {"):src.index("locked_sweep() {")]
    (tmp_path / "harness").mkdir(exist_ok=True)
    for name, word in (("desk_launch.sh", "DESK_LAUNCH"), ("remote_inbox.sh", "PUBLISH"),
                       ("deploy_agent.sh", "DEPLOY_AGENT"), ("revise_agent.sh", "REVISE_AGENT")):
        f = tmp_path / "harness" / name
        f.write_text(f'#!/usr/bin/env bash\necho "{word} $*"\n')
        f.chmod(0o755)
    script = textwrap.dedent("""\
        set -uo pipefail
        REPO="$1"
        say() {{ echo "SAY $*"; }}
        aq_role() {{ echo "{role}"; }}
        watchdog() {{ echo WATCHDOG; }}
        setsid() {{ "$@"; }}
        nohup() {{ "$@"; }}
        gh() {{
          case "$1 $2" in
            "auth status") return 0 ;;
            "pr list") printf '7\\tresearch/a-b\\tx\\n' ;;
          esac
        }}
        """).format(role=role) + body + "\nsweep\n"
    p = subprocess.run(["bash", "-c", script, "bash", str(tmp_path)],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout


def test_the_desk_sweep_launches_merges_and_runs_no_agent(tmp_path):
    out = _sweep(tmp_path, "desk")
    assert "WATCHDOG" in out and "DESK_LAUNCH" in out and "PUBLISH" in out
    assert "DEPLOY_AGENT" not in out and "REVISE_AGENT" not in out


def test_the_research_sweep_runs_agents_and_watches_no_strategy(tmp_path):
    out = _sweep(tmp_path, "research")
    assert "WATCHDOG" not in out, "the research host trades nothing; restarting would double it"
    assert "DESK_LAUNCH" not in out
    assert "DEPLOY_AGENT 7" in out


def test_the_single_host_sweep_is_unchanged(tmp_path):
    out = _sweep(tmp_path, "all")
    assert "WATCHDOG" in out and "DEPLOY_AGENT 7" in out and "DESK_LAUNCH" not in out


# ------------------------------------------------- dashboard over the synced files

@pytest.fixture
def remote(tmp_path, monkeypatch):
    r = tmp_path / "remote"
    for d in ("desktop/logs", "desktop/sessions", "desktop/transcripts", "outbox/requests"):
        (r / d).mkdir(parents=True)
    monkeypatch.setenv("AQ_REMOTE_DIR", str(r))
    monkeypatch.setattr(dashboard, "SESSIONS_DIR", str(tmp_path / "local-sessions"))
    (tmp_path / "local-sessions").mkdir()
    return r


def _heartbeat(remote, age_s, **extra):
    hb = remote / "desktop" / "heartbeat.json"
    hb.write_text(json.dumps({"ts": "x", "host": "desktop-h0g6rel", "running": [UUID]} | extra))
    t = time.time() - age_s
    os.utime(hb, (t, t))


def _remote_session(remote, status="running"):
    (remote / "desktop" / "sessions" / f"{UUID}.json").write_text(json.dumps({
        "id": UUID, "kind": "research", "target": "spot-btc", "status": status,
        "pid": 1, "cwd": "/home/seleis/autoQuant", "model": "opus",
        "log": "harness/logs/research-spot-btc-20261201T000000Z.log",
        "launched_at": "2026-12-01T00:00:00+00:00"}))


def test_a_research_host_session_is_listed_and_its_pid_never_probed(remote, monkeypatch):
    _heartbeat(remote, 30)
    _remote_session(remote)
    monkeypatch.setattr(os, "kill", lambda *a: pytest.fail("probed a remote pid locally"))
    dashboard.refresh_sessions()
    [row] = dashboard.CACHE.get("sessions")
    assert row["host"] == "desktop" and row["status"] == "running"


def test_a_session_on_a_silent_research_host_is_not_shown_running(remote):
    _heartbeat(remote, dashboard.REMOTE_STALE_S + 60)
    _remote_session(remote)
    dashboard.refresh_sessions()
    [row] = dashboard.CACHE.get("sessions")
    assert row["status"] == "aborted" and row["reason"] == "host_offline"


def test_research_host_status(remote):
    assert dashboard.research_host()["seen"] is False
    _heartbeat(remote, 30, research_today="2026-12-01", disk_free_gb=812.5)
    h = dashboard.research_host()
    assert h["online"] and h["research_today"] == "2026-12-01" and h["running"] == [UUID]


def test_research_host_logs_and_transcripts_are_served(remote, logs_dir):
    _remote_session(remote, status="done")
    (remote / "desktop" / "logs" / "research-spot-btc-20261201T000000Z.log").write_text("hi\n")
    (remote / "desktop" / "transcripts" / f"{UUID}.jsonl").write_text("")
    assert dashboard.log_path("research-spot-btc-20261201T000000Z.log")
    reg, host = dashboard._registry(UUID)
    assert host == "desktop"
    assert dashboard.transcript_path(reg, host) == str(
        remote / "desktop" / "transcripts" / f"{UUID}.jsonl")
    dashboard.refresh_agents()
    [run_] = dashboard.CACHE.get("agents")
    assert run_["host"] == "desktop" and run_["session"] == UUID


def test_a_synced_symlink_cannot_reach_outside_the_inbox(remote, logs_dir, tmp_path):
    secret = tmp_path / "secret.log"
    secret.write_text("root only\n")
    os.symlink(secret, remote / "desktop" / "logs" / "evil.log")
    assert dashboard.log_path("evil.log") is None


def _no_local_agents(monkeypatch):
    """`sh` may still ask the CLI its version (the model picker); it may not launch."""
    real = dashboard.sh

    def sh(cmd, *a, **k):
        if cmd and cmd[0] in (dashboard.RESEARCH, dashboard.RESUME):
            pytest.fail(f"started an agent on the desk: {cmd}")
        return real(cmd, *a, **k)
    monkeypatch.setattr(dashboard, "sh", sh)


def test_the_desk_queues_research_instead_of_launching(remote, monkeypatch):
    monkeypatch.setenv("AQ_ROLE", "desk")
    _no_local_agents(monkeypatch)
    r = dashboard.do_action({"action": "launch_research", "asset_class": "spot-btc",
                             "seed": "funding skew", "model": "opus"})
    assert r["ok"] is True and "queued" in r["output"]
    [f] = list((remote / "outbox" / "requests").glob("*.json"))
    req = json.loads(f.read_text())
    assert req["action"] == "launch_research" and req["asset_class"] == "spot-btc"
    assert req["model"] == "opus" and req["seed"] == "funding skew"


def test_the_desk_still_validates_before_queueing(remote, monkeypatch):
    monkeypatch.setenv("AQ_ROLE", "desk")
    assert dashboard.do_action({"action": "launch_research",
                                "asset_class": "dogecoin"})["ok"] is False
    assert dashboard.do_action({"action": "resume_session",
                                "session": "../../x"})["ok"] is False
    assert not list((remote / "outbox" / "requests").glob("*.json"))


def test_the_desk_queues_resumes(remote, monkeypatch):
    monkeypatch.setenv("AQ_ROLE", "desk")
    _no_local_agents(monkeypatch)
    monkeypatch.setattr(dashboard, "refresh_sessions", lambda: None)
    assert dashboard.do_action({"action": "resume_session", "session": UUID})["ok"]
    [f] = list((remote / "outbox" / "requests").glob("*.json"))
    req = json.loads(f.read_text())
    assert req["action"] == "resume" and req["session"] == UUID


def test_queueing_without_the_inbox_says_how_to_set_it_up(tmp_path, monkeypatch):
    monkeypatch.setenv("AQ_ROLE", "desk")
    monkeypatch.setenv("AQ_REMOTE_DIR", str(tmp_path / "nope"))
    r = dashboard.do_action({"action": "launch_research", "asset_class": "spot-btc"})
    assert r["ok"] is False and "remote_inbox.sh setup" in r["error"]
