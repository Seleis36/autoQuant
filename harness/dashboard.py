"""autoQuant control dashboard -- stdlib HTTP server, no framework.

    ./harness/dashboard.sh start          # daemonised
    .venv/bin/python harness/dashboard.py --bind auto --port 8787

Serves `harness/web/index.html` plus a small JSON API. Every slow source (GitHub,
Binance, Claude transcripts) is refreshed on a background thread and served from
cache, so the page stays responsive and a GitHub outage degrades one panel instead
of hanging the request.

Binding
-------
`--bind auto` (default) binds loopback plus the Tailscale address if this host has
one, and nothing else. That is deliberate: the API can place orders, spend money on
agents and stop strategies, so it must never land on a coffee-shop Wi-Fi interface.
Under WSL's default NAT the tailnet address lives on the Windows side and is not
bindable from here -- see harness/README.md for the mirrored-networking fix.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics  # noqa: E402
from live_lib import (BASE_URL, LIVE_DIR, REPO_ROOT, PaperBroker,  # noqa: E402
                      _read_allocations, load_env)

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HARNESS_DIR, "web")
STATE_DIR = os.path.join(HARNESS_DIR, "state")
RUN_DIR = os.path.join(STATE_DIR, "run")
LOGS_DIR = os.path.join(HARNESS_DIR, "logs")
LAUNCH = os.path.join(HARNESS_DIR, "launch_live.sh")
POLLER = os.path.join(HARNESS_DIR, "poll_prs.sh")
RESEARCH = os.path.join(HARNESS_DIR, "launch_research.sh")

ASSET_CLASSES = ["spot-btc", "spot-eth", "crypto-perps", "crypto-alts", "us-large-cap",
                 "sector-etf", "global-equity-etf", "fx-majors", "rates-bonds",
                 "commodities", "vol-complex"]

# Approximate Claude pricing, $/Mtok, for the local usage estimate only.
PRICING = {
    "opus":   {"in": 15.0, "out": 75.0, "cache_w": 18.75, "cache_r": 1.50},
    "sonnet": {"in": 3.0,  "out": 15.0, "cache_w": 3.75,  "cache_r": 0.30},
    "haiku":  {"in": 1.0,  "out": 5.0,  "cache_w": 1.25,  "cache_r": 0.10},
}


def _tier(model: str) -> str:
    m = (model or "").lower()
    for t in ("opus", "sonnet", "haiku"):
        if t in m:
            return t
    return "sonnet"


def sh(cmd, timeout=30, cwd=REPO_ROOT):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timed out"
    except Exception as e:  # noqa: BLE001
        return 1, "", str(e)


# --------------------------------------------------------------------------- cache

class Cache:
    """Values refreshed on a background thread; readers never block on the network."""

    def __init__(self):
        self._d = {}
        self._lock = threading.Lock()

    def get(self, key, default=None):
        with self._lock:
            v = self._d.get(key)
        return default if v is None else v["value"]

    def age(self, key):
        with self._lock:
            v = self._d.get(key)
        return None if v is None else time.time() - v["at"]

    def set(self, key, value):
        with self._lock:
            self._d[key] = {"value": value, "at": time.time()}


CACHE = Cache()


# --------------------------------------------------------------------------- sources

def strategy_dirs() -> list:
    out = []
    for meta in sorted(glob.glob(os.path.join(LIVE_DIR, "*", "*", "meta.json"))):
        out.append(os.path.relpath(os.path.dirname(meta), LIVE_DIR))
    for runner in sorted(glob.glob(os.path.join(LIVE_DIR, "*", "*", "runner.py"))):
        n = os.path.relpath(os.path.dirname(runner), LIVE_DIR)
        if n not in out:
            out.append(n)
    return out


def _read_json(path, default=None):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return default


def systemd_unit(name: str) -> str:
    rc, out, _ = sh(["systemd-escape", name], 10)
    return f"autoquant-strategy@{out}.service" if rc == 0 else ""


def pid_of(name: str):
    """Live pid, asking systemd first -- a supervised strategy has no pidfile of
    its own, so the pidfile alone would report everything as stopped."""
    unit = systemd_unit(name)
    if unit:
        rc, out, _ = sh(["systemctl", "--user", "show", unit, "-p", "MainPID",
                         "--value"], 10)
        if rc == 0 and out.isdigit() and out != "0":
            return int(out)
        rc, out, _ = sh(["systemctl", "--user", "is-enabled", unit], 10)
        if rc == 0:
            return None          # systemd owns it and says it is not up
    pf = os.path.join(RUN_DIR, name.replace("/", "_") + ".pid")
    if not os.path.exists(pf):
        return None
    try:
        pid = int(open(pf).read().strip())
        os.kill(pid, 0)
        return pid
    except Exception:  # noqa: BLE001
        return None


def proc_started(pid):
    try:
        with open(f"/proc/{pid}/stat") as fh:
            starttime = int(fh.read().split(")")[-1].split()[19])
        with open("/proc/uptime") as fh:
            up = float(fh.read().split()[0])
        hz = os.sysconf("SC_CLK_TCK")
        return time.time() - (time.time() - up + starttime / hz)
    except Exception:  # noqa: BLE001
        return None


SCHED_S = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600,
           "2h": 7200, "4h": 14400, "6h": 21600, "12h": 43200, "1d": 86400}


def build_strategies() -> list:
    out = []
    for name in strategy_dirs():
        d = os.path.join(LIVE_DIR, name)
        meta = _read_json(os.path.join(d, "meta.json"), {}) or {}
        state = _read_json(os.path.join(d, "state.json"), {}) or {}
        ledger = _read_json(os.path.join(d, "ledger.json"), {}) or {}
        sched = meta.get("schedule") or state.get("schedule") or "1h"
        pid = pid_of(name)

        # A hung process still reports RUNNING; staleness is what actually catches it.
        stale, last_run_age = False, None
        if state.get("last_run"):
            try:
                lr = datetime.fromisoformat(state["last_run"].replace("Z", "+00:00"))
                last_run_age = (datetime.now(timezone.utc) - lr).total_seconds()
                stale = last_run_age > 2.2 * SCHED_S.get(sched, 3600)
            except Exception:  # noqa: BLE001
                pass

        status = "RUNNING" if pid else "STOPPED"
        if pid and stale:
            status = "STALE"

        started = proc_started(pid) if pid else None
        out.append({
            "name": name, "meta": meta, "state": state, "ledger": ledger,
            "schedule": sched, "symbol": meta.get("symbol") or state.get("symbol"),
            "pid": pid, "status": status, "stale": stale,
            "supervised": bool(systemd_unit(name)) and sh(
                ["systemctl", "--user", "is-enabled", systemd_unit(name)], 10)[0] == 0,
            "last_run_age_s": last_run_age,
            "uptime_s": (time.time() - started) if started else None,
            "shadow": state.get("shadow", ledger.get("shadow")),
            "live": metrics.compute(name, sched),
        })
    return out


def refresh_prs():
    rc, out, _ = sh(["gh", "pr", "list", "--state", "open", "--limit", "50", "--json",
                     "number,title,isDraft,labels,headRefName,url,updatedAt,author"], 45)
    if rc != 0:
        return
    try:
        prs = json.loads(out or "[]")
    except json.JSONDecodeError:
        return
    for p in prs:
        p["labelNames"] = [l["name"] for l in p.get("labels", [])]
    CACHE.set("prs", prs)


def refresh_account():
    try:
        b = PaperBroker("BTCUSDT")
        bals = b.account_balances()
        px = b.mark_price()
        CACHE.set("account", {
            "venue": BASE_URL, "ok": True,
            "usdt_free": bals.get("USDT", {}).get("free", 0.0),
            "btc_total": bals.get("BTC", {}).get("free", 0.0) + bals.get("BTC", {}).get("locked", 0.0),
            "btc_price": px,
            "allocations": _read_allocations(),
        })
    except Exception as e:  # noqa: BLE001
        CACHE.set("account", {"venue": BASE_URL, "ok": False, "error": str(e),
                              "allocations": _read_allocations()})


def refresh_usage():
    """Rolling Claude usage from local transcripts.

    These token counts come straight from API responses, so they are exact for this
    machine -- but they are NOT your subscription quota. `/usage` is the only source
    for that and it is not available outside an interactive session. Usage from
    claude.ai, mobile or another machine is invisible here, and the weighting each
    token type gets against the 5h/weekly limits is not published.
    """
    now = datetime.now(timezone.utc)
    seen, buckets = set(), {"5h": {}, "7d": {}}
    for f in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        try:
            fh = open(f)
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = d.get("message") or {}
                u = msg.get("usage")
                mid = msg.get("id")
                if not u or not mid or mid in seen:
                    continue          # streaming repeats the same message many times
                seen.add(mid)
                try:
                    ts = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00"))
                except Exception:  # noqa: BLE001
                    continue
                age = (now - ts).total_seconds()
                for label, span in (("5h", 5 * 3600), ("7d", 7 * 86400)):
                    if age <= span:
                        t = _tier(msg.get("model"))
                        b = buckets[label].setdefault(
                            t, {"in": 0, "out": 0, "cache_w": 0, "cache_r": 0, "msgs": 0})
                        b["in"] += u.get("input_tokens", 0)
                        b["out"] += u.get("output_tokens", 0)
                        b["cache_w"] += u.get("cache_creation_input_tokens", 0)
                        b["cache_r"] += u.get("cache_read_input_tokens", 0)
                        b["msgs"] += 1
    res = {}
    for label, tiers in buckets.items():
        cost = sum(sum(v[k] / 1e6 * PRICING[t][k] for k in ("in", "out", "cache_w", "cache_r"))
                   for t, v in tiers.items())
        tot = {k: sum(v[k] for v in tiers.values())
               for k in ("in", "out", "cache_w", "cache_r", "msgs")}
        res[label] = {"tokens": tot, "cost_usd": cost, "by_tier": tiers}
    res["disclaimer"] = ("Exact token counts from local Claude Code transcripts. NOT your "
                         "subscription quota -- the 5h/weekly limits are server-side and "
                         "/usage is unavailable outside an interactive session.")
    CACHE.set("usage", res)


def refresh_data_freshness():
    out = []
    for p in sorted(glob.glob(os.path.join(REPO_ROOT, "data", "*.parquet"))):
        age = time.time() - os.path.getmtime(p)
        out.append({"file": os.path.basename(p), "age_h": age / 3600,
                    "mb": os.path.getsize(p) / 1e6})
    out.sort(key=lambda r: -r["age_h"])
    CACHE.set("data", out)


def refresh_git():
    _, branch, _ = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], 10)
    _, head, _ = sh(["git", "log", "-1", "--format=%h %s"], 10)
    _, remote, _ = sh(["git", "remote", "get-url", "origin"], 10)
    url = re.sub(r"^git@github\.com:", "https://github.com/", remote or "")
    url = re.sub(r"\.git$", "", url)
    CACHE.set("git", {"branch": branch, "head": head, "url": url})


def refresh_agents():
    runs = []
    for f in sorted(glob.glob(os.path.join(LOGS_DIR, "*.log")), key=os.path.getmtime,
                    reverse=True)[:25]:
        base = os.path.basename(f)
        runs.append({"log": base, "mtime": os.path.getmtime(f),
                     "size": os.path.getsize(f),
                     "kind": "deploy" if base.startswith("pr-") else
                             ("research" if base.startswith("research-") else "other")})
    CACHE.set("agents", runs)


def poller_status():
    pf = os.path.join(STATE_DIR, "poller.pid")
    if os.path.exists(pf):
        try:
            pid = int(open(pf).read().strip())
            os.kill(pid, 0)
            return {"running": True, "pid": pid}
        except Exception:  # noqa: BLE001
            pass
    return {"running": False, "pid": None}


REFRESHERS = [(refresh_prs, 120), (refresh_account, 45), (refresh_usage, 120),
              (refresh_data_freshness, 300), (refresh_git, 120), (refresh_agents, 30)]


def refresher_loop(stop: threading.Event):
    last = {}
    while not stop.is_set():
        for fn, every in REFRESHERS:
            if time.time() - last.get(fn.__name__, 0) >= every:
                try:
                    fn()
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                last[fn.__name__] = time.time()
        stop.wait(5)


# --------------------------------------------------------------------------- actions

def do_action(body: dict) -> dict:
    a = body.get("action")
    name = body.get("strategy", "")
    if name and (".." in name or not re.fullmatch(r"[\w.-]+/[\w.-]+", name)):
        return {"ok": False, "error": "bad strategy name"}

    if a in ("start", "stop", "restart"):
        rc, out, err = sh([LAUNCH, a, name], 120)
        return {"ok": rc == 0, "output": out or err}
    if a == "flatten":
        rc, out, err = sh([os.path.join(REPO_ROOT, ".venv/bin/python"), "-c",
                           "import sys;sys.path.insert(0,'harness');"
                           "from live_lib import PaperBroker;import json,os;"
                           f"d=os.path.join('live','{name}');"
                           "m=json.load(open(os.path.join(d,'meta.json')));"
                           "b=PaperBroker(m['symbol'],capital_usdt=m.get('capital_usdt',2500),"
                           "state_file=os.path.join(d,'ledger.json'));b.preflight();"
                           "print(json.dumps(b.flatten(),default=str))"], 90)
        return {"ok": rc == 0, "output": out or err}
    if a == "kill_all":
        results = []
        for s in strategy_dirs():
            sh([LAUNCH, "stop", s], 60)
            results.append(s)
        return {"ok": True, "output": "stopped: " + ", ".join(results)}
    if a == "flatten_all":
        outs = []
        for s in strategy_dirs():
            outs.append(do_action({"action": "flatten", "strategy": s}).get("output", ""))
        return {"ok": True, "output": "\n".join(outs)}
    if a in ("poller_start", "poller_stop"):
        rc, out, err = sh([POLLER, "--start" if a == "poller_start" else "--stop"], 60)
        return {"ok": rc == 0, "output": out or err}
    if a == "poller_sweep":
        rc, out, err = sh([POLLER, "--once"], 600)
        return {"ok": rc == 0, "output": out or err}
    if a == "requeue_pr":
        num = str(body.get("pr", "")).strip()
        if not num.isdigit():
            return {"ok": False, "error": "bad pr number"}
        for lab in ("invalid", "harness:failed", "harness:processing"):
            sh(["gh", "pr", "edit", num, "--remove-label", lab], 30)
        try:
            os.remove(os.path.join(STATE_DIR, f"attempts-{num}"))
        except OSError:
            pass
        refresh_prs()
        return {"ok": True, "output": f"PR #{num} requeued"}
    if a == "launch_research":
        ac = body.get("asset_class", "")
        if ac not in ASSET_CLASSES:
            return {"ok": False, "error": "unknown asset class"}
        seed = (body.get("seed") or "")[:500]
        rc, out, err = sh([RESEARCH, ac, seed], 60)
        return {"ok": rc == 0, "output": out or err}
    return {"ok": False, "error": f"unknown action {a!r}"}


# --------------------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    server_version = "autoQuant"

    def log_message(self, fmt, *args):
        pass                      # the access log is noise here

    def _send(self, code, payload, ctype="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(
            payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = self.path.split("?")[0]
        qs = dict(p.split("=", 1) for p in self.path.split("?")[1].split("&")
                  if "=" in p) if "?" in self.path else {}
        if path in ("/", "/index.html"):
            f = os.path.join(WEB_DIR, "index.html")
            if not os.path.exists(f):
                return self._send(404, b"index.html missing", "text/plain")
            return self._send(200, open(f, "rb").read(), "text/html; charset=utf-8")
        if path == "/api/state":
            strategies = build_strategies()
            return self._send(200, {
                "now": datetime.now(timezone.utc).isoformat(),
                "strategies": strategies,
                "correlation": metrics.correlation(
                    [s["name"] for s in strategies],
                    {s["name"]: s["schedule"] for s in strategies}),
                "poller": poller_status(),
                "prs": CACHE.get("prs", []),
                "account": CACHE.get("account", {}),
                "usage": CACHE.get("usage", {}),
                "data": CACHE.get("data", []),
                "git": CACHE.get("git", {}),
                "agents": CACHE.get("agents", []),
                "asset_classes": ASSET_CLASSES,
                "ages": {k: CACHE.age(k) for k in
                         ("prs", "account", "usage", "data", "git", "agents")},
            })
        if path == "/api/series":
            name = qs.get("strategy", "")
            if not re.fullmatch(r"[\w.-]+/[\w.-]+", name or ""):
                return self._send(400, {"error": "bad strategy"})
            return self._send(200, metrics.equity_series(name))
        if path == "/api/journal":
            name = qs.get("strategy", "")
            if not re.fullmatch(r"[\w.-]+/[\w.-]+", name or ""):
                return self._send(400, {"error": "bad strategy"})
            rows = [r for r in metrics.read_journal(name) if r.get("event") != "heartbeat"]
            return self._send(200, rows[-200:])
        if path == "/api/log":
            name = qs.get("strategy", "")
            n = min(int(qs.get("n", 200) or 200), 2000)
            if re.fullmatch(r"[\w.-]+/[\w.-]+", name or ""):
                f = os.path.join(LIVE_DIR, name, "runner.log")
            elif qs.get("file", "").replace("%2F", "/") and "/" not in qs.get("file", ""):
                f = os.path.join(LOGS_DIR, qs["file"])
            else:
                return self._send(400, {"error": "bad target"})
            if not os.path.exists(f):
                return self._send(404, {"error": "no log"})
            _, out, _ = sh(["tail", "-n", str(n), f], 20)
            return self._send(200, {"text": out})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/action":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:  # noqa: BLE001
            return self._send(400, {"ok": False, "error": "bad body"})
        try:
            return self._send(200, do_action(body))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"ok": False, "error": str(e)})


def tailscale_ip():
    """This host's tailnet address, if it is bindable from here."""
    for pat in ("100.", ):
        try:
            out = subprocess.run(["ip", "-4", "-o", "addr"], capture_output=True,
                                 text=True, timeout=10).stdout
        except Exception:  # noqa: BLE001
            return None
        for line in out.splitlines():
            m = re.search(r"inet (100\.\d+\.\d+\.\d+)/", line)
            if m:
                return m.group(1)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default="auto",
                    help="'auto' (loopback + tailnet), or an explicit address")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    load_env()

    if args.bind == "auto":
        addrs = ["127.0.0.1"]
        ts = tailscale_ip()
        if ts:
            addrs.append(ts)
        else:
            print("NOTE: no tailnet address is bindable from this host, so the dashboard "
                  "is loopback-only.\n      Under WSL's default NAT the Tailscale address "
                  "lives on the Windows side; see\n      harness/README.md "
                  "(mirrored networking) to reach it from your phone.", flush=True)
    else:
        addrs = [args.bind]

    stop = threading.Event()
    threading.Thread(target=refresher_loop, args=(stop,), daemon=True).start()

    servers = []
    for a in addrs:
        try:
            srv = ThreadingHTTPServer((a, args.port), Handler)
        except OSError as e:
            print(f"WARNING: cannot bind {a}:{args.port}: {e}", flush=True)
            continue
        servers.append(srv)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"listening on http://{a}:{args.port}", flush=True)
    if not servers:
        print("ERROR: no address could be bound", file=sys.stderr)
        return 1
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        stop.set()
        for s in servers:
            s.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
