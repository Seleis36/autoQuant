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
