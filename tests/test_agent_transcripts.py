"""Full agent conversations on the dashboard, alias resolution, and the nightly batch.

The harness log holds only an agent's opening prompt and final answer; the conversation
in between is in Claude Code's own transcript, keyed by the session id the harness mints.
"""
import json
import os
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from conftest import REPO_ROOT

import dashboard
import transcript

SID = "070f152b-1e09-4c67-879d-d5e6ababad96"


def _jsonl(*records):
    return "".join(json.dumps(r) + "\n" for r in records)


TRANSCRIPT = _jsonl(
    {"type": "queue-operation", "content": "/spot-btc-quant-research"},
    {"type": "user", "timestamp": "2026-09-12T06:31:01Z",
     "message": {"role": "user", "content": "/spot-btc-quant-research 2+ sharpe"}},
    {"type": "assistant", "timestamp": "2026-09-12T06:31:05Z",
     "message": {"model": "claude-opus-5-5", "content": [
         {"type": "thinking", "thinking": ""},                       # redacted: dropped
         {"type": "text", "text": "Reviewing past ideas first."},
         {"type": "tool_use", "id": "t1", "name": "Bash",
          "input": {"command": "ls past_research", "description": "List past research"}}]}},
    {"type": "user", "timestamp": "2026-09-12T06:31:06Z",
     "message": {"content": [{"type": "tool_result", "tool_use_id": "t1",
                              "content": "x" * (transcript.MAX_TOOL_OUTPUT + 500)}]}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1",
                                              "is_error": True,
                                              "content": [{"type": "text", "text": "boom"}]}]}},
    {"type": "attachment", "attachment": {"type": "environment"}},
) + '{"type": "assistant", "message": {"content": [{"type": "te'   # live run, half a line


@pytest.fixture
def projects(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    d = transcript.project_dir(REPO_ROOT)
    os.makedirs(d)
    return d


def test_project_dir_matches_claude_codes_naming(monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/x")
    assert transcript.project_dir("/home/seleis/autoQuant") == \
        "/x/projects/-home-seleis-autoQuant"
    assert transcript.project_dir("/a/b_c.d") == "/x/projects/-a-b-c-d"


def test_render_keeps_the_conversation_and_folds_the_noise(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text(TRANSCRIPT)
    out = transcript.render(str(f))
    kinds = [e["kind"] for e in out["entries"]]
    assert kinds == ["user", "assistant", "tool_use", "tool_result", "tool_result"]
    assert out["model"] == "claude-opus-5-5"
    use = out["entries"][2]
    assert use["tool"] == "Bash" and "# List past research\nls past_research" == use["text"]
    big = out["entries"][3]
    assert big["tool"] == "Bash", "a result is labelled with the call it answers"
    assert big["clipped"] and "more characters not shown" in big["text"]
    assert out["entries"][4]["error"] is True and out["entries"][4]["text"] == "boom"


# ------------------------------------------------------------------ /api/transcript

@pytest.fixture
def server(logs_dir, tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(dashboard, "SESSIONS_DIR", str(sessions))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", sessions
    srv.shutdown()
    srv.server_close()


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


@pytest.mark.parametrize("bad", ["", "../../etc/passwd", SID + ".jsonl", SID.upper(),
                                 "070f152b"])
def test_transcript_refuses_anything_but_a_session_id(server, bad):
    base, _ = server
    code, body = get(f"{base}/api/transcript?session={bad}")
    assert code == 400


def test_transcript_404s_cleanly_when_the_file_is_gone(server, projects):
    base, _ = server
    code, body = get(f"{base}/api/transcript?session={SID}")
    assert code == 404 and "transcript" in body["error"]


def test_transcript_is_served_with_its_registry_context(server, projects):
    base, sessions = server
    (sessions / f"{SID}.json").write_text(json.dumps(
        {"id": SID, "kind": "research", "target": "spot-btc", "status": "done",
         "model": "opus", "cwd": REPO_ROOT}))
    with open(os.path.join(projects, f"{SID}.jsonl"), "w") as fh:
        fh.write(TRANSCRIPT)
    code, body = get(f"{base}/api/transcript?session={SID}")
    assert code == 200
    assert body["target"] == "spot-btc" and body["model"] == "claude-opus-5-5"
    assert len(body["entries"]) == 5


# ------------------------------------------------------------- registry read-backs

@pytest.mark.parametrize("usage,want", [
    ({"claude-haiku-4-5-20251001": {}, "claude-opus-5-5": {}}, "claude-opus-5-5"),
    ({"claude-opus-5[1m]": {}}, "claude-opus-5"),
    ({"claude-haiku-4-5-20251001": {}}, "claude-haiku-4-5-20251001"),
    ({}, None),
])
def test_resolved_model_ignores_the_housekeeping_model(tmp_path, usage, want):
    f = tmp_path / "r.json"
    f.write_text(json.dumps({"modelUsage": usage}))
    assert dashboard.resolved_model(str(f)) == want


def test_resolved_model_is_none_before_a_run_finishes(tmp_path):
    assert dashboard.resolved_model(str(tmp_path / "missing.json")) is None


def test_agent_run_logs_link_back_to_their_session(logs_dir, tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(dashboard, "SESSIONS_DIR", str(sessions))
    (sessions / f"{SID}.json").write_text(json.dumps(
        {"id": SID, "log": "harness/logs/research-spot-btc-X.log"}))
    (sessions / f"{SID}.result.json").write_text("{}")
    (logs_dir / "research-spot-btc-X.log").write_text("hi")
    (logs_dir / "nightly-X.log").write_text("hi")
    dashboard.refresh_agents()
    runs = {r["log"]: r for r in dashboard.CACHE.get("agents")}
    assert runs["research-spot-btc-X.log"]["session"] == SID
    assert runs["nightly-X.log"]["session"] is None


# --------------------------------------------------------------- shell: classifier

def classify(result: dict, tmp_path, rc=1):
    f = tmp_path / "result.json"
    f.write_text(json.dumps(result))
    script = f'. "{REPO_ROOT}/harness/session_lib.sh"; session_classify {rc} /dev/null "{f}"'
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                          timeout=30).stdout.strip()


def test_running_out_of_usage_credits_is_resumable_not_a_crash(tmp_path):
    """Observed verbatim on a Fable run: subtype "success" with is_error set."""
    msg = ("You're out of usage credits. Switch to another model, or manage usage "
           "credits at claude.ai/settings/usage?from=cc_cli_limit_message, to continue.")
    assert classify({"subtype": "success", "is_error": True, "result": msg},
                    tmp_path) == "usage_limit"


def test_a_clean_result_is_still_clean(tmp_path):
    assert classify({"subtype": "success", "is_error": False, "result": "PR opened"},
                    tmp_path, rc=0) == "clean"


def test_claude_bin_prefers_the_self_updating_native_install(tmp_path):
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    native = home / ".local" / "bin" / "claude"
    script = f'unset CLAUDE_BIN; HOME="{home}"; . "{REPO_ROOT}/harness/session_lib.sh"; echo "$CLAUDE_BIN"'
    run = lambda: subprocess.run(["bash", "-c", script], capture_output=True,
                                 text=True, timeout=30).stdout.strip()
    assert run() == "claude"
    native.write_text("#!/bin/sh\n")
    native.chmod(0o755)
    assert run() == str(native)


# ------------------------------------------------------------ shell: nightly batch

def test_nightly_script_parses():
    p = subprocess.run(["bash", "-n", os.path.join(REPO_ROOT, "harness",
                                                   "nightly_research.sh")],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def _dry(env):
    e = dict(os.environ, **env)
    p = subprocess.run([os.path.join(REPO_ROOT, "harness", "nightly_research.sh"),
                        "--dry-run"], capture_output=True, text=True, timeout=60, env=e)
    assert p.returncode == 0, p.stderr
    return p.stdout.split("tonight:")[1].split("(")[0].split()


def test_nightly_picks_distinct_real_asset_classes():
    commands = {f[:-len("-quant-research.md")] for f in
                os.listdir(os.path.join(REPO_ROOT, ".claude", "commands"))
                if f.endswith("-quant-research.md")}
    picks = _dry({"NIGHTLY_COUNT": "2"})
    assert len(picks) == 2 and len(set(picks)) == 2
    assert set(picks) <= commands
    assert set(_dry({"NIGHTLY_COUNT": "99"})) == commands


def test_nightly_honours_an_explicit_list():
    assert _dry({"NIGHTLY_CLASSES": "fx-majors spot-eth"}) == ["fx-majors", "spot-eth"]
