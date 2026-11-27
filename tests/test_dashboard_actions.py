"""The POST /api/action layer: validation, honesty of results, and the flatten shell-out."""
import ast
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import dashboard
from conftest import write_strategy


@pytest.fixture
def server(live_dir, logs_dir):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def post(base, payload, raw=None, headers=None):
    data = raw if raw is not None else json.dumps(payload).encode()
    req = urllib.request.Request(base + "/api/action", data=data, method="POST",
                                 headers=headers or {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


# --------------------------------------------------------------------- name validation

@pytest.mark.parametrize("name", [
    "../../etc/passwd", "a/b/c", "noslash", "spot-btc/..", "spot btc/x", "spot-btc/x;rm",
])
def test_bad_strategy_names_are_refused(name):
    r = dashboard.do_action({"action": "stop", "strategy": name})
    assert r["ok"] is False and r["error"] == "bad strategy name"


def test_unknown_action_is_refused():
    r = dashboard.do_action({"action": "definitely-not-an-action"})
    assert r["ok"] is False and "unknown action" in r["error"]


def test_unknown_asset_class_is_refused():
    r = dashboard.do_action({"action": "launch_research", "asset_class": "dogecoin"})
    assert r["ok"] is False and r["error"] == "unknown asset class"


def test_requeue_needs_a_numeric_pr():
    assert dashboard.do_action({"action": "requeue_pr", "pr": "3; rm -rf /"})["ok"] is False
    assert dashboard.do_action({"action": "requeue_pr", "pr": ""})["ok"] is False


def test_resume_needs_a_uuid():
    r = dashboard.do_action({"action": "resume_session", "session": "not-a-uuid"})
    assert r["ok"] is False and r["error"] == "bad session id"


# --------------------------------------------------------------------- flatten shell-out

def test_flatten_source_is_valid_python_and_reads_argv():
    """The strategy name is passed as argv rather than spliced into the source. The
    regex bars quotes today, but a validator and a code generator drifting apart is
    exactly how that stops being true."""
    ast.parse(dashboard.FLATTEN_SRC)
    assert "sys.argv[1]" in dashboard.FLATTEN_SRC
    assert "{" not in dashboard.FLATTEN_SRC.replace("{}", ""), "no f-string interpolation"


def test_flatten_without_a_strategy_is_refused():
    r = dashboard.do_action({"action": "flatten"})
    assert r["ok"] is False


@pytest.mark.parametrize("action", ["start", "stop", "restart", "flatten"])
def test_an_empty_strategy_name_is_refused(action, monkeypatch):
    """An empty name passes the regex guard (which only runs `if name`) and reaches
    launch_live.sh as an empty argument, where it resolves to live/ itself."""
    called = []
    monkeypatch.setattr(dashboard, "sh",
                        lambda cmd, *a, **k: (called.append(cmd), (0, "", ""))[1])
    r = dashboard.do_action({"action": action, "strategy": ""})
    assert r["ok"] is False
    assert called == [], "nothing should have been executed"


# --------------------------------------------------------------------- bulk actions

def test_kill_all_reports_failures_rather_than_a_tick(monkeypatch, live_dir):
    """A kill switch that answers ok:True having stopped nothing is worse than useless."""
    write_strategy(live_dir, "spot-btc/a")
    write_strategy(live_dir, "spot-eth/b")
    monkeypatch.setattr(dashboard, "sh",
                        lambda cmd, *a, **k: (1, "", "systemctl: unit not found"))
    r = dashboard.do_action({"action": "kill_all"})
    assert r["ok"] is False
    assert "FAILED" in r["output"]
    assert "spot-btc/a" in r["output"] and "spot-eth/b" in r["output"]


def test_kill_all_is_ok_when_every_stop_succeeds(monkeypatch, live_dir):
    write_strategy(live_dir, "spot-btc/a")
    monkeypatch.setattr(dashboard, "sh", lambda cmd, *a, **k: (0, "stopped", ""))
    r = dashboard.do_action({"action": "kill_all"})
    assert r["ok"] is True and "spot-btc/a" in r["output"]


def test_flatten_all_propagates_a_failure(monkeypatch, live_dir):
    write_strategy(live_dir, "spot-btc/a")
    monkeypatch.setattr(dashboard, "sh", lambda cmd, *a, **k: (1, "", "venue down"))
    r = dashboard.do_action({"action": "flatten_all"})
    assert r["ok"] is False and "venue down" in r["output"]


# --------------------------------------------------------------------- request handling

def test_oversized_body_is_rejected(server):
    status, body = post(server, None, raw=b"x",
                        headers={"Content-Type": "application/json",
                                 "Content-Length": str(dashboard.MAX_BODY_BYTES + 1)})
    assert status == 413


def test_a_non_object_body_is_rejected(server):
    status, body = post(server, [1, 2, 3])
    assert status == 400
    assert "object" in body["error"]


def test_malformed_json_is_a_400_not_a_500(server):
    status, body = post(server, None, raw=b"{not json")
    assert status == 400


def test_post_to_an_unknown_path_is_404(server):
    req = urllib.request.Request(server + "/api/nope", data=b"{}", method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=10)
    assert e.value.code == 404


# ------------------------------------------------------------- research model picker
#
# The dashboard is reachable over the tailnet and this value reaches a subprocess argv,
# so the model is an allowlist key, never a free-text string that is passed through.

class _Calls(list):
    """Only the launcher invocations; `sh` also runs `claude --version` for the picker."""

    @property
    def launches(self):
        return [c for c in self if c and c[0] == dashboard.RESEARCH]


@pytest.fixture
def captured_launch(monkeypatch):
    calls = _Calls()
    monkeypatch.setattr(dashboard, "sh",
                        lambda cmd, *a, **k: (calls.append(cmd), (0, "started", ""))[1])
    return calls


def test_the_default_model_is_the_latest_opus_alias(server, captured_launch):
    """A pinned id went stale the day Opus 5.5 shipped; the alias follows the CLI."""
    code, body = post(server, {"action": "launch_research", "asset_class": "spot-btc"})
    assert body["ok"] is True
    assert captured_launch.launches[0][-2:] == ["--model", "opus"]


def test_no_offered_model_is_pinned_to_a_version():
    for m in dashboard.RESEARCH_MODELS.values():
        assert not any(ch.isdigit() for ch in m["id"]), m["id"]


@pytest.mark.parametrize("key,model_id", [
    ("opus", "opus"),
    ("sonnet", "sonnet"),
    ("fable", "fable"),
])
def test_each_offered_model_launches_on_its_alias(server, captured_launch, key, model_id,
                                                  monkeypatch):
    monkeypatch.setattr(dashboard, "_cli_version", lambda: "2.2.0")
    code, body = post(server, {"action": "launch_research", "asset_class": "fx-majors",
                               "model": key})
    assert body["ok"] is True
    assert captured_launch.launches[0][-2:] == ["--model", model_id]


@pytest.mark.parametrize("bad", ["haiku", "claude-opus-5", "opus[1m]", "",
                                 "--dangerously-skip-permissions"])
def test_a_model_outside_the_allowlist_is_refused(server, captured_launch, bad):
    code, body = post(server, {"action": "launch_research", "asset_class": "spot-btc",
                               "model": bad})
    if bad == "":
        assert body["ok"] is True          # empty falls back to the default
    else:
        assert body["ok"] is False and "model" in body["error"]
        assert captured_launch.launches == [], "nothing may be launched on a rejected model"


def test_a_model_the_installed_cli_cannot_run_is_refused_before_launching(
        server, captured_launch, monkeypatch):
    """The agent is detached, so an unsupported model would otherwise surface as a session
    that died minutes later with the reason buried in a log."""
    monkeypatch.setattr(dashboard, "research_model_options", lambda: [
        {"key": "fable", "id": "fable", "label": "Fable (latest)",
         "unavailable": "needs Claude Code >= 2.1.251; this machine has 2.1.114."}])
    code, body = post(server, {"action": "launch_research", "asset_class": "spot-btc",
                               "model": "fable"})
    assert body["ok"] is False
    assert "2.1.251" in body["error"]
    assert captured_launch.launches == []


def test_model_options_mark_an_unsupported_model_rather_than_hiding_it(monkeypatch):
    monkeypatch.setattr(dashboard, "_cli_version", lambda: "2.1.114")
    opts = {o["key"]: o for o in dashboard.research_model_options()}
    assert set(opts) == set(dashboard.RESEARCH_MODELS)
    assert "unavailable" in opts["fable"] and "2.1.251" in opts["fable"]["unavailable"]
    assert "unavailable" not in opts["opus"]
    assert opts["opus"]["default"] is True


def test_a_new_enough_cli_offers_every_model(monkeypatch):
    monkeypatch.setattr(dashboard, "_cli_version", lambda: "2.2.0")
    assert all("unavailable" not in o for o in dashboard.research_model_options())


@pytest.mark.parametrize("have,want,below", [
    ("2.1.114", "2.1.251", True), ("2.1.251", "2.1.251", False),
    ("2.1.300", "2.1.251", False), ("2.2.0", "2.1.251", False),
    ("3.0.0", "2.1.251", False), ("2.0.999", "2.1.251", True),
])
def test_version_comparison_is_numeric_not_lexicographic(have, want, below):
    assert dashboard._version_below(have, want) is below


@pytest.mark.parametrize("model,tier", [
    ("claude-fable-5-1", "fable"), ("claude-opus-5", "opus"), ("claude-opus-5-5", "opus"),
    ("opus", "opus"), ("sonnet", "sonnet"),
    ("claude-sonnet-5", "sonnet"), ("claude-haiku-4-5", "haiku"),
])
def test_usage_is_priced_against_the_right_tier(model, tier):
    """Fable used to fall through to the sonnet fallback and be costed at a fifth."""
    assert dashboard._tier(model) == tier
    assert dashboard.PRICING[tier]["in"] > 0


def test_the_picker_shows_what_an_alias_last_resolved_to(monkeypatch):
    """"Latest" is only checkable if the page says what latest turned out to be."""
    monkeypatch.setattr(dashboard, "_cli_version", lambda: "2.2.0")
    monkeypatch.setattr(dashboard.CACHE, "get", lambda k, d=None: [
        {"model": "opus", "model_resolved": "claude-opus-5-5"},
        {"model": "opus", "model_resolved": "claude-opus-5"},      # older, listed later
    ] if k == "sessions" else d)
    opts = {o["key"]: o for o in dashboard.research_model_options()}
    assert opts["opus"]["resolved"] == "claude-opus-5-5"
    assert "resolved" not in opts["sonnet"]


# --------------------------------------------------------------------- cross-site guards
#
# The API can place orders and spend money on agents, so it must not be drivable from a
# page that merely happens to be open in the operator's browser.

def test_a_text_plain_body_is_refused(server):
    """A hidden <form enctype=text/plain> can send this cross-site without a preflight."""
    status, body = post(server, None, raw=b'{"action": "kill_all"}',
                        headers={"Content-Type": "text/plain"})
    assert status == 403 and "Content-Type" in body["error"]


def test_a_foreign_origin_is_refused(server):
    status, body = post(server, {"action": "kill_all"},
                        headers={"Content-Type": "application/json",
                                 "Origin": "https://evil.example"})
    assert status == 403 and "cross-origin" in body["error"]


def test_a_same_origin_post_is_served(server):
    port = server.rsplit(":", 1)[1]
    status, body = post(server, {"action": "no-such-action"},
                        headers={"Content-Type": "application/json",
                                 "Origin": f"http://127.0.0.1:{port}"})
    assert status == 200 and "unknown action" in body["error"]


def test_a_rebound_host_name_is_refused(server):
    """DNS rebinding: the socket is ours but the browser still says attacker's name."""
    status, body = post(server, {"action": "kill_all"},
                        headers={"Content-Type": "application/json",
                                 "Host": "evil.example", "Origin": "http://evil.example"})
    assert status == 403 and "host" in body["error"]


def test_a_configured_public_host_is_served(server, monkeypatch):
    """The name Cloudflare Tunnel forwards with must be admitted via DASHBOARD_HOSTS."""
    monkeypatch.setenv("DASHBOARD_HOSTS", "quant.example.com, other.example")
    status, body = post(server, {"action": "no-such-action"},
                        headers={"Content-Type": "application/json",
                                 "Host": "quant.example.com",
                                 "Origin": "https://quant.example.com"})
    assert status == 200 and "unknown action" in body["error"]


@pytest.mark.parametrize("host,ok", [
    ("127.0.0.1:8788", True), ("localhost", True), ("[::1]:8788", True),
    ("box.tail1234.ts.net", True), ("evil.example", False), ("", False),
    ("127.0.0.1.evil.example", False),
])
def test_host_allowlist(host, ok, monkeypatch):
    monkeypatch.delenv("DASHBOARD_HOSTS", raising=False)
    assert dashboard.host_allowed(host, "127.0.0.1") is ok
