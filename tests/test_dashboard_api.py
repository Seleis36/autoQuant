"""HTTP-level tests for the dashboard API.

These drive a real server over a real socket rather than calling the handler methods
directly, because the bugs they cover lived in the gap between what the browser sends
(percent-encoded) and what the server parsed (raw).
"""
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from conftest import write_strategy

import dashboard


@pytest.fixture
def server(live_dir, logs_dir):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def get(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return r.status, json.load(r)


def get_err(base, path):
    """Return (status, payload) for a response the server rejects."""
    try:
        return get(base, path)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


# --------------------------------------------------------------- percent-encoded names
#
# Every deployment is "<asset-class>/<short-name>", so the browser always sends the
# strategy as `spot-btc%2Fbult`. The old hand-rolled query parser never decoded it, so
# the name matched no pattern and all three per-strategy endpoints failed at once:
# Log answered "bad target", Trades answered "bad strategy" (which the frontend then
# tried to .filter, throwing "rows.filter is not a function"), and every sparkline
# silently rendered empty.

NAME = "spot-btc/bult"
ENCODED = urllib.parse.quote(NAME, safe="")


def test_encoded_slash_is_decoded_by_query_parser():
    assert ENCODED == "spot-btc%2Fbult"          # what fetch() actually puts on the wire


def test_log_accepts_percent_encoded_strategy(server, live_dir):
    write_strategy(live_dir, NAME, runner_log="line one\nline two\n")
    status, body = get(server, f"/api/log?strategy={ENCODED}&n=50")
    assert status == 200
    assert "line two" in body["text"]


def test_journal_returns_a_list_for_percent_encoded_strategy(server, live_dir):
    write_strategy(live_dir, NAME, journal_rows=[
        {"ts": "2026-01-01T00:00:00+00:00", "event": "rebalance", "equity": 100.0,
         "price": 50.0, "weight": 1.0, "traded": True, "side": "BUY"},
        {"ts": "2026-01-01T01:00:00+00:00", "event": "heartbeat"},
    ])
    status, body = get(server, f"/api/journal?strategy={ENCODED}")
    # A dict here is what produced "rows.filter is not a function" in the browser.
    assert isinstance(body, list), f"expected a JSON array, got {body!r}"
    assert [r["event"] for r in body] == ["rebalance"], "heartbeats must be filtered out"


def test_series_accepts_percent_encoded_strategy(server, live_dir):
    write_strategy(live_dir, NAME, journal_rows=[
        {"ts": f"2026-01-01T0{i}:00:00+00:00", "event": "rebalance",
         "equity": 100.0 + i, "price": 50.0, "weight": 1.0, "shadow": False}
        for i in range(4)
    ])
    status, body = get(server, f"/api/series?strategy={ENCODED}")
    assert status == 200
    assert len(body["equity"]) == 4
    assert body["equity"][0] == 100.0          # normalised to 100 at the segment start


def test_log_by_file_accepts_encoded_name(server, logs_dir):
    (logs_dir / "pr-3-20260909T071010Z.log").write_text("agent output\n")
    status, body = get(
        server, "/api/log?file=" + urllib.parse.quote("pr-3-20260909T071010Z.log") + "&n=10")
    assert status == 200
    assert "agent output" in body["text"]


# --------------------------------------------------------------------------- validation

@pytest.mark.parametrize("bad", [
    "",                                  # missing
    "noslash",                           # not <class>/<name>
    "a/b/c",                             # too deep
    urllib.parse.quote("../../etc", safe=""),
])
def test_series_rejects_bad_strategy_names(server, bad):
    status, body = get_err(server, f"/api/series?strategy={bad}")
    assert status == 400
    assert "error" in body


def test_log_rejects_path_traversal_in_file(server):
    # Decoding the query string is what makes this reachable at all, so it has to be
    # rejected *after* decoding, not before.
    status, body = get_err(
        server, "/api/log?file=" + urllib.parse.quote("../../../etc/passwd", safe=""))
    assert status == 400
    assert body["error"] == "bad target"


def test_log_rejects_non_log_extension(server, logs_dir):
    (logs_dir / "secrets.env").write_text("KEY=abc\n")
    status, _ = get_err(server, "/api/log?file=secrets.env")
    assert status == 400


def test_log_rejects_non_numeric_line_count(server, live_dir):
    # int(qs["n"]) used to be unguarded, so `?n=abc` was a 500 with a traceback.
    write_strategy(live_dir, NAME, runner_log="x\n")
    status, body = get_err(server, f"/api/log?strategy={ENCODED}&n=abc")
    assert status == 400
    assert body["error"] == "bad line count"


def test_log_line_count_is_clamped(server, live_dir):
    write_strategy(live_dir, NAME, runner_log="x\n" * 10)
    for n in ("0", "-5", "999999"):
        status, _ = get(server, f"/api/log?strategy={ENCODED}&n={n}")
        assert status == 200


def test_missing_log_is_404_not_400(server, live_dir):
    write_strategy(live_dir, NAME)               # no runner.log written
    status, body = get_err(server, f"/api/log?strategy={ENCODED}")
    assert status == 404
    assert body["error"] == "no log"


def test_unknown_path_is_404(server):
    status, _ = get_err(server, "/api/nope")
    assert status == 404
