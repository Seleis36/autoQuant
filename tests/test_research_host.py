"""The research host's own scripts (harness/research_host): the once-a-day batch rule and
its guards, and the validation of the requests the desk's dashboard leaves for it. Nothing
here launches an agent: daily.sh runs only with --dry-run, and the request handler is
driven with requests it must refuse."""
import importlib.util
import json
import os
import subprocess
import textwrap

import pytest

from conftest import REPO_ROOT

RH = os.path.join(REPO_ROOT, "harness", "research_host")
UUID = "0123abcd-0000-4000-8000-00000000beef"


def _load_handler():
    spec = importlib.util.spec_from_file_location(
        "handle_requests", os.path.join(RH, "handle_requests.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hr = _load_handler()


# ------------------------------------------------------------------- daily.sh

@pytest.fixture
def daily_env(tmp_path):
    """A logged-in `claude` and `gh`, a private state dir and log, and AQ_ROLE=research."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "claude").write_text('#!/usr/bin/env bash\necho \'{"loggedIn": true}\'\n')
    (bindir / "gh").write_text("#!/usr/bin/env bash\nexit 0\n")
    for f in bindir.iterdir():
        f.chmod(0o755)
    state = tmp_path / "state"
    env = dict(os.environ, AQ_ROLE="research", AQ_RH_STATE=str(state),
               AQ_DAILY_LOG=str(tmp_path / "daily.log"), CLAUDE_BIN=str(bindir / "claude"),
               PATH=f"{bindir}:{os.environ['PATH']}")
    return env, state, bindir


def daily(env, today, *args):
    return subprocess.run([os.path.join(RH, "daily.sh"), "--dry-run", *args],
                          capture_output=True, text=True, timeout=120, cwd=REPO_ROOT,
                          env=dict(env, AQ_DAILY_TODAY=today))


def test_daily_runs_once_per_day(daily_env):
    env, state, _ = daily_env
    first = daily(env, "2099-01-01")
    assert first.returncode == 0, first.stdout + first.stderr
    assert "guards passed" in first.stdout
    assert (state / "last_batch").read_text().strip() == "2099-01-01"
    second = daily(env, "2099-01-01")
    assert second.returncode == 0 and "already ran today" in second.stdout
    assert "guards passed" not in second.stdout
    assert "guards passed" in daily(env, "2099-01-02").stdout       # a new day runs


@pytest.mark.parametrize("marker, why", [("paused", "paused"),
                                         ("skip-2099-01-01", "skip-2099-01-01 is set")])
def test_daily_off_switches_do_not_use_up_the_day(daily_env, marker, why):
    env, state, _ = daily_env
    state.mkdir()
    (state / marker).touch()
    p = daily(env, "2099-01-01")
    assert p.returncode == 0 and why in p.stdout
    assert not (state / "last_batch").exists()


def test_daily_skips_when_claude_is_logged_out(daily_env):
    env, state, bindir = daily_env
    (bindir / "claude").write_text('#!/usr/bin/env bash\necho \'{"loggedIn": false}\'\n')
    p = daily(env, "2099-01-01")
    assert "claude is not logged in" in p.stdout
    assert not (state / "last_batch").exists()


def test_daily_skips_on_low_disk(daily_env):
    env, state, _ = daily_env
    p = daily(dict(env, DAILY_MIN_FREE_GB="99999999"), "2099-01-01")
    assert "GB free on the distro disk" in p.stdout
    assert not (state / "last_batch").exists()


def test_daily_dry_run_never_stamps_the_real_state(daily_env):
    env, _, _ = daily_env
    env = {k: v for k, v in env.items() if k != "AQ_RH_STATE"}
    real = os.path.join(REPO_ROOT, "harness", "state", "research_host", "last_batch")
    before = open(real).read() if os.path.exists(real) else None
    daily(env, "2099-01-01")
    after = open(real).read() if os.path.exists(real) else None
    assert before == after


@pytest.mark.parametrize("script", ["daily.sh", "sync.sh", "install.sh"])
@pytest.mark.parametrize("role", ["desk", ""])
def test_research_host_scripts_refuse_other_roles(tmp_path, script, role):
    env = {k: v for k, v in os.environ.items() if k != "AQ_ROLE"}
    env["AQ_ROLE"] = role or "all"
    p = subprocess.run([os.path.join(RH, script), "--dry-run"], capture_output=True,
                       text=True, timeout=60, cwd=REPO_ROOT, env=env)
    assert p.returncode == 5 and "REFUSED" in p.stderr


# ------------------------------------------------------------- request validation

def test_valid_requests_become_argv():
    argv, why = hr.validate({"action": "launch_research", "asset_class": "fx-majors",
                             "seed": "carry; $(rm -rf ~)", "model": "sonnet"})
    assert why is None
    assert argv[1:] == ["fx-majors", "carry; $(rm -rf ~)", "--model", "sonnet"]
    assert os.path.basename(argv[0]) == "launch_research.sh"
    assert hr.validate({"action": "resume", "session": UUID})[0][1:] == [UUID]
    assert hr.validate({"action": "resume", "session": "--all"})[0][1:] == ["--all"]
    assert hr.validate({"action": "clear_attempts", "pr": 27})[0] == ["clear_attempts", "27"]
    assert hr.validate({"action": "clear_attempts", "pr": "27"})[0] == ["clear_attempts", "27"]


@pytest.mark.parametrize("req", [
    {"action": "launch_research", "asset_class": "spot-btc; id", "seed": "", "model": "opus"},
    {"action": "launch_research", "asset_class": "../spot-btc", "seed": "", "model": "opus"},
    {"action": "launch_research", "asset_class": "spot-btc", "seed": "x", "model": "gpt-5"},
    {"action": "launch_research", "asset_class": "spot-btc", "seed": "x" * 501, "model": "opus"},
    {"action": "launch_research", "asset_class": "spot-btc", "seed": ["x"], "model": "opus"},
    {"action": "resume", "session": "--all; id"},
    {"action": "resume", "session": UUID + "\n"},
    {"action": "resume"},
    {"action": "clear_attempts", "pr": "27/../../x"},
    {"action": "clear_attempts", "pr": True},
    {"action": "clear_attempts", "pr": -1},
    {"action": "shell", "cmd": "id"},
    ["not", "an", "object"],
])
def test_bad_requests_are_refused(req):
    argv, why = hr.validate(req)
    assert argv is None and why


def test_handler_drops_refused_requests_and_logs_them(tmp_path, monkeypatch):
    pending = tmp_path / "p"
    pending.mkdir()
    (pending / "20261127T000001-aa.json").write_text(json.dumps({"action": "shell"}))
    (pending / "20261127T000002-ab.json").write_text("not json")
    (pending / "bad name.json").write_text("{}")
    log = tmp_path / "requests.log"
    monkeypatch.setattr(hr, "LOG", str(log))
    hr.main(str(pending))
    assert list(pending.iterdir()) == []
    lines = log.read_text().splitlines()
    assert len(lines) == 3 and all("REJECTED" in ln for ln in lines)


def test_a_launch_with_no_free_slot_waits_and_logs_once(tmp_path, monkeypatch):
    pending = tmp_path / "p"
    pending.mkdir()
    f = pending / "20261127T000001-aa.json"
    f.write_text(json.dumps({"action": "launch_research", "asset_class": "spot-btc",
                             "seed": "", "model": "opus"}))
    monkeypatch.setattr(hr, "LOG", str(tmp_path / "requests.log"))
    calls = []

    class Done:
        returncode, stdout, stderr = hr.NO_SLOT, "", "slots full"

    monkeypatch.setattr(hr.subprocess, "run", lambda argv, **kw: calls.append(argv) or Done)
    hr.main(str(pending))
    hr.main(str(pending))
    assert f.exists() and len(calls) == 2
    assert (tmp_path / "requests.log").read_text().count("WAITING") == 1
    Done.returncode = 0
    hr.main(str(pending))
    assert not f.exists() and not os.path.exists(str(f) + ".waiting")
